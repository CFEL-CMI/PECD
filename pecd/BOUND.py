#!/usr/bin/env python3
# -*- coding: utf-8; fill-column: 120 -*-
#
# Copyright (C) 2021 Emil Zak <emil.zak@cfel.de>
#

import input
import MAPPING
import POTENTIAL
import GRID 

import numpy as np
from scipy import sparse
from scipy.special import sph_harm
import quadpy

import sys
import time


def BUILD_HMAT0(params):

    maparray, Nbas = MAPPING.GENMAP( params['bound_nlobs'], params['bound_nbins'], params['bound_lmax'], \
                                     params['map_type'], params['working_dir'] )


    if params['hmat_format'] == 'csr':
        hmat = sparse.csr_matrix((Nbas, Nbas), dtype=np.float64)
    elif params['hmat_format'] == 'regular':
        hmat = np.zeros((Nbas, Nbas), dtype=np.float64)


    """ calculate hmat """
    BUILD_POTMAT0(params)

    """ diagonalize hmat """
    start_time = time.time()
    enr0, coeffs0 = np.linalg.eigh(hmat, UPLO = 'U')
    end_time = time.time()
    print("Time for diagonalization of field-free Hamiltonian: " +  str("%10.3f"%(end_time-start_time)) + "s")


    if params['save_ham0'] == True:
        if params['hmat_format'] == 'csr':
            sparse.save_npz( params['working_dir'] + params['file_hmat0'] , hmat , compressed = False )
        elif params['hmat_format'] == 'regular':
            with open( params['working_dir'] + params['file_hmat0'] , 'w') as hmatfile:   
                np.savetxt(hmatfile, hmat, fmt = '%10.4e')

    if params['save_psi0'] == True:
        psi0file = open(params['working_dir'] + params['file_psi0'], 'w')
        for ielem,elem in enumerate(maparray):
            psi0file.write( " %5d"%elem[0] +  " %5d"%elem[1] + "  %5d"%elem[2] + \
                            " %5d"%elem[3] +  " %5d"%elem[4] + "\t" + \
                            "\t ".join('{:10.5e}'.format(coeffs0[ielem,v]) for v in range(0,params['num_ini_vec'])) + "\n")

    if params['save_enr0'] == True:
        with open(params['working_dir'] + params['file_enr0'], "w") as energyfile:   
            np.savetxt( energyfile, enr0 , fmt='%10.5f' )
  
    print(hmat)

def BUILD_KEOMAT0(params):
    print("under construction")


def BUILD_POTMAT0(params):

    rgrid, Nr = GRID.r_grid( params['bound_nlobs'], params['bound_nbins'], params['bound_binw'],  params['bound_rshift'] )

    print("Interpolating electrostatic potential")
    esp_interpolant = POTENTIAL.INTERP_POT(params)

    if  params['gen_adaptive_quads'] == True:
        sph_quad_list = gen_adaptive_quads( params, esp_interpolant, rgrid )
    else:
        sph_quad_list = read_adaptive_quads(params)

    print("sph_quad_list")
    print(sph_quad_list )
    GRID.GEN_GRID(sph_quad_list)



def calc_interp_sph(interpolant,r,theta,phi):
    x = r * np.sin(theta) * np.cos(phi)
    y = r * np.sin(theta) * np.sin(phi)
    z = r * np.cos(theta)
    return interpolant(x,y,z)

def calc_potmatelem_quadpy( l1, m1, l2, m2, rin, scheme, esp_interpolant ):
    """calculate single element of the potential matrix on an interpolated potential"""
    myscheme = quadpy.u3.schemes[scheme]()
    """
    Symbols: 
            theta_phi[0] = theta in [0,pi]
            theta_phi[1] = phi  in [-pi,pi]
            sph_harm(m1, l1,  theta_phi[1]+np.pi, theta_phi[0])) means that we 
                                                                 put the phi angle in range [0,2pi] and 
                                                                 the  theta angle in range [0,pi] as required by 
                                                                 the scipy special funciton sph_harm
    """
    val = myscheme.integrate_spherical(lambda theta_phi: np.conjugate( sph_harm( m1, l1,  theta_phi[1]+np.pi, theta_phi[0] ) ) \
                                                                     * sph_harm( m2, l2, theta_phi[1]+np.pi, theta_phi[0] ) \
                                                                     * calc_interp_sph( esp_interpolant, rin, theta_phi[0], theta_phi[1]+np.pi) ) 

    return val

def read_adaptive_quads(params):
    levels = []
    quadfilename = params['working_dir'] + params['file_quad_levels'] 
    fl = open( quadfilename , 'r' )
    for line in fl:
        words   = line.split()
        i       = int(words[0])
        n       = int(words[1])
        xi      = int(words[2])
        scheme  = str(words[3])
        levels.append([i,n,xi,scheme])
    return levels

def gen_adaptive_quads(params, esp_interpolant, rgrid):

    sph_quad_list = [] #list of quadrature levels needed to achieve convergence quad_tol of the potential energy matrix elements (global)

    lmax = params['bound_lmax']
    quad_tol = params['sph_quad_tol']

    print("Testing potential energy matrix elements using Lebedev quadratures")

    sphlist = MAPPING.GEN_SPHLIST(lmax)

    val =  np.zeros( shape = ( len(sphlist)**2 ), dtype=complex)
    val_prev = np.zeros( shape = ( len(sphlist)**2 ), dtype=complex)

    spherical_schemes = []
    for elem in list(quadpy.u3.schemes.keys()):
        if 'lebedev' in elem:
            spherical_schemes.append(elem)
    xi = 0
    for i in range(np.size( rgrid, axis=0 )): 
        for n in range(np.size( rgrid, axis=1 )): 
            rin = rgrid[i,n]
            print("i = " + str(i) + ", n = " + str(n) + ", xi = " + str(xi) + ", r = " + str(rin) )
            if rin <= params['r_cutoff']:
                for scheme in spherical_schemes[3:]: #skip 003a,003b,003c rules
                    k=0
                    for l1,m1 in sphlist:
                        for l2,m2 in sphlist:
                        
                            val[k] = calc_potmatelem_quadpy( l1, m1, l2, m2, rin, scheme, esp_interpolant )
                            print(  '%4d %4d %4d %4d'%(l1,m1,l2,m2) + '%12.6f %12.6fi' % (val[k].real, val[k].imag) + \
                                    '%12.6f %12.6fi' % (val_prev[k].real, val_prev[k].imag) + \
                                    '%12.6f %12.6fi' % (np.abs(val[k].real-val_prev[k].real), np.abs(val[k].imag-val_prev[k].imag)) + \
                                    '%12.6f '%np.abs(val[k]-val_prev[k])  )
                            k += 1

                    diff = np.abs(val - val_prev)

                    if (np.any( diff > quad_tol )):
                        print( str(scheme) + " convergence not reached" ) 
                        for k in range(len(val_prev)):
                            val_prev[k] = val[k]
                    elif ( np.all( diff < quad_tol ) ):     
                        print( str(scheme) + " convergence reached !!!")
                        sph_quad_list.append([ i, n, xi, str(scheme)])
                        xi += 1
                        break

                    #if no convergence reached raise warning
                    if ( scheme == spherical_schemes[len(spherical_schemes)-1] and np.any( diff > quad_tol )):
                        print("WARNING: convergence at tolerance level = " + str(quad_tol) + " not reached for all considered quadrature schemes")
                        exit()
            else:
                scheme == spherical_schemes[lmax+2]
                sph_quad_list.append([ i, n, xi, str(scheme)])
                xi += 1


    print("Converged quadrature levels: ")
    print(sph_quad_list)
    quadfilename = params['working_dir'] + params['file_quad_levels'] 
    fl = open(quadfilename,'w')
    print("saving quadrature levels to file: " + quadfilename )
    for item in sph_quad_list:
        fl.write( str('%4d '%item[0]) + str('%4d '%item[1]) + str('%4d '%item[2]) + str(item[3]) + "\n")

    return sph_quad_list

if __name__ == "__main__":      

    params = input.gen_input()
    BUILD_HMAT0(params)
